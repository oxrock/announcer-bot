from rlbot.utils.structures.game_interface import GameInterface
from rlbot.utils.structures.game_data_struct import GameTickPacket,FieldInfoPacket
from rlbot.utils.structures.ball_prediction_struct import BallPrediction
from rlbot.utils.logging_utils import get_logger
from utils import *
import pyttsx3
from queue import Queue
import threading
import random
import time
import math

def host(_queue):
    engine = pyttsx3.init()
    rate = engine.getProperty("rate")
    voices = engine.getProperty('voices')  # list of available voices
    comment_storage = []
    accepting = True

    def pick_best_comment(comment_list):
        current_highest = 0
        best_comments = []

        for index,_comment in enumerate(comment_list):
            if _comment.priority > current_highest:
                best_comments.clear()
                current_highest = _comment.priority
                best_comments.append(_comment)
            elif _comment.priority == current_highest:
                best_comments.append(_comment)

        if len(best_comments) > 0:
            earliest_time = math.inf
            earliest_comment = 0
            for index,_comment in enumerate(best_comments):
                if _comment.time_generated < earliest_time:
                    earliest_comment = index
                    earliest_time = _comment.time_generated
            return earliest_comment
        else:
            return -1




    if len(voices) < 1:
        print("no usable voices found on this pc, exiting")
        return

    print("Announcer initialized!")
    last_comment = None
    while accepting or len(comment_storage) > 0:

        while not _queue.empty() and accepting:
            c = _queue.get()
            if c.comment != "exit":
                comment_storage.append(c)
            else:
                accepting = False

        for c in comment_storage:
            c.update()
            #remove duplicates, won't work as well when we add better variety
            if last_comment != None:
                if c.comment == last_comment.comment:
                    if c.time_generated - last_comment.time_generated <10:
                        c.valid = False


        comment_storage = [c for c in comment_storage if c.valid ]
        c_index = pick_best_comment(comment_storage)
        if c_index != -1:
            comment = comment_storage.pop(c_index)
            #might want to increase speaking rate depending on size of current comment storage
            # if comment == "exit":
            #     print("Recieved exit message!")
            #     break
            try:
                engine.setProperty('voice', voices[comment.voiceID].id)
            except:
                engine.setProperty('voice', voices[0].id)

            engine.say(comment.comment)
            engine.runAndWait()
            last_comment = comment

    print("Exiting announcer thread.")


class Commentator():
    def __init__(self):
        self.game_interface = GameInterface(get_logger("Commentator"))
        self.game_interface.load_interface()
        self.game_interface.wait_until_loaded()
        self.touchTimer = 0
        self.currentTime = 0
        self.firstIter = True
        self.overTime = False
        self.shotDetection = True
        self.currentZone = None
        self.ballHistory = []
        self.lastTouches = []
        self.teams = []
        self.joinTimer = 0
        self.packet = GameTickPacket()
        self.f_packet = FieldInfoPacket()
        self.ball_predictions = BallPrediction()
        self.q = Queue(maxsize=20)
        self.host = threading.Thread(target=host, args=(self.q,))
        self.host.start()
        self.main()
        self.host.join()

    def reset(self):
        self.touchTimer = 0
        self.currentTime = 0
        self.firstIter = True
        self.overTime = False
        self.shotDetection = True
        self.ballHistory = []
        self.lastTouches = []
        self.teams = []
        self.joinTimer = 0
        with self.q.mutex:
            self.q.queue.clear()

    def speak(self, phrase,priority,decayRate):
        if not self.q.full():
            self.q.put(Comment(phrase, random.randint(0, 1),priority,decayRate))

    def timeCheck(self, newTime):
        if newTime - self.currentTime < -1:
            return True
        self.currentTime = newTime
        return False

    def overtimeCheck(self,packet):
        if not self.overTime:
            if packet.game_info.is_overtime:
                self.overTime = True
                self.speak(f"That's the end of regulation time, we're headed into over time with the score tied at {packet.teams[0].score}!",10,1)

    def gameWrapUp(self):
        if self.teams[0].score > self.teams[1].score:
            winner = "Blue"
        else:
            winner = "Orange"

        if abs(self.teams[0].score - self.teams[1].score) >=4:
            self.speak(f"Team {winner} has won today's match with a dominant performance.",10,1)
            #impressive victory
        else:
            #normal win message
            self.speak(f"Team {winner} clinched the victory this match",10,1)

        self.speak("Thank you all for watching today's game and never forget that Diablo is coming for you. G G everyone.",10,1)

    def stopHost(self):
        while self.q.full():
            pass
        self.speak("exit",0,0)

    def handleShotDetection(self):
        if self.shotDetection:
            if len(self.ballHistory) > 0:
                shot,goal = shotDetection(self.ball_predictions,2,self.currentTime)
                if shot:
                    if not self.q.full():
                        if self.lastTouches[-1].team == goal:
                            #self.speak(f"That's a potential own goal from {self.lastTouches[-1].player_name}.",5,3)
                            pass
                        else:
                            self.speak(f"{self.lastTouches[-1].player_name} takes a shot at the enemy net!",5,3)
                    self.shotDetection = False




    def updateTouches(self, packet):
        contactNames = ["hit","touch","contact"]

        try:
            touch = ballTouch(packet.game_ball.latest_touch)
        except Exception as e:
            touch = None
            print(e)

        if touch:
            if len(self.lastTouches) < 1 or self.lastTouches[-1] != touch:
                self.lastTouches.append(touch)
                self.shotDetection = True
                for team in self.teams:
                    team.update(touch)
            #no more spam from touches for now

    def zone_analysis(self,ball_obj):
        corners = [0,1,2,3]
        boxes = [4,5]
        sides = [6,7]
        new_zone = find_current_zone(ball_obj)
        if self.currentZone == None:
            self.currentZone = new_zone
            return

        if new_zone != self.currentZone:
            if self.currentZone in sides:
                if new_zone in sides:
                    self.speak(f"The ball crosses into {get_team_color_by_zone(new_zone)} territory.",0,1)

                elif new_zone in boxes:
                    if self.shotDetection:
                        self.speak(f"The ball is dangerously close to the {get_team_color_by_zone(new_zone)} goal!",2,2)

                elif new_zone in corners:
                    self.speak(
                        f" {self.lastTouches[-1].player_name} hits the ball to the {get_team_color_by_zone(new_zone)} corner.",1,2)


            elif self.currentZone in boxes:
                #leaving the box is worth mentioning
                self.speak(f"The ball is cleared out of the {get_team_color_by_zone(self.currentZone)} box by {self.lastTouches[-1].player_name}.",2,2)

            elif new_zone in corners:
                self.speak(
                    f" {self.lastTouches[-1].player_name} hits the ball to the {get_team_color_by_zone(new_zone)} corner.",1,2)

            elif new_zone in boxes:
                if self.shotDetection:
                    self.speak(f"The ball is dangerously close to the {get_team_color_by_zone(new_zone)} goal!",2,2)

            self.currentZone = new_zone



    def updateGameBall(self,packet):
        if packet.game_info.is_round_active:
            currentBall = ballObject(packet.game_ball)
            self.ballHistory.append(currentBall)
            self.zone_analysis(currentBall)

        if len(self.ballHistory) >1000:
            del self.ballHistory[0]

    def gatherMatchData(self, packet):
        members = [[], []]
        for i in range(packet.num_cars):
            _car = Car(packet.game_cars[i].name, packet.game_cars[i].team, i)
            members[_car.team].append(_car)

        self.teams.append(Team(0, members[0]))
        self.teams.append(Team(1, members[1]))
        self.speak(
            f"Welcome to today's match. On team blue we have {', '.join([x.name for x in self.teams[0].members])} ",10,10)
        self.speak(
            f" and representing the orange team we have {', '.join([x.name for x in self.teams[1].members])} .",10,10)
        self.speak("Good luck everyone.",10,10)

    def scoreAnnouncement(self,teamIndex):
        try:
            scorer = self.teams[teamIndex].lastTouch.player_name
            speed = self.ballHistory[-1].getRealSpeed()
            if not self.q.full():
                if speed <= 20:
                    self.speak(f"{scorer} scores! It barely limped across the goal line at {speed} kilometers per hour, but a goal is a goal.",8,10)

                elif speed >= 100:
                    self.speak(f"{scorer} scores on a blazingly fast shot at  {speed} kilometers per hour! What a shot!",8,10)

                else:
                    self.speak(f"And {scorer}'s shot goes in at {speed} kilometers per hour!",8,10)

            if not self.q.full():
                self.speak(f"That goal brings the score to {self.teams[0].score} blue and {self.teams[1].score} orange.",8,10)
        except:
            pass

    def scoreCheck(self, packet):
        if self.teams[0].score != packet.teams[0].score:
            self.teams[0].score = packet.teams[0].score
            self.scoreAnnouncement(0)
            self.currentZone = 0

        if self.teams[1].score != packet.teams[1].score:
            self.teams[1].score = packet.teams[1].score
            self.scoreAnnouncement(1)
            self.currentZone = 0

    def main(self):
        while True:
            self.game_interface.update_live_data_packet(self.packet)
            self.game_interface.update_field_info_packet(self.f_packet)
            self.game_interface.update_ball_prediction(self.ball_predictions)
            #gametime = "{:.2f}".format(self.packet.game_info.seconds_elapsed)

            if self.packet.game_info.is_match_ended:
                print("Game is over, exiting.")
                self.gameWrapUp()
                self.stopHost()
                break

            if self.firstIter:
                if self.packet.num_cars >= 1:
                    if self.joinTimer <= 0:
                        self.joinTimer = time.time()
                    if time.time() - self.joinTimer >=1: #arbitrary timer to ensure all cars connected
                        self.firstIter = False
                        self.currentTime = float(self.packet.game_info.seconds_elapsed)
                        self.gatherMatchData(self.packet)

            if self.timeCheck(float(self.packet.game_info.seconds_elapsed)):
                print("framework reset, resetting announcerbot")
                self.reset()
            if not self.firstIter:
                self.updateGameBall(self.packet)
                self.updateTouches(self.packet)
                self.handleShotDetection()
                self.scoreCheck(self.packet)
                self.overtimeCheck(self.packet)


if __name__ == "__main__":
    s = Commentator()
    print("Exited commentator class")