from rlbot.utils.structures.game_interface import GameInterface
from rlbot.utils.structures.game_data_struct import GameTickPacket
from rlbot.utils.logging_utils import get_logger
from utils import *
import pyttsx3
import psutil
from queue import Queue
import threading
import random
import time
import math

def host(_queue):
    engine = pyttsx3.init()
    rate = engine.getProperty("rate")
    voices = engine.getProperty('voices')  # list of available voices
    if len(voices) < 1:
        print("no usable voices found on this pc, exiting")
        return

    print("Announcer initialized!")
    while True:
        if not _queue.empty():
            comment = _queue.get()
            engine.setProperty("rate",rate+(_queue.qsize()*10))
            if comment == "exit":
                print("Recieved exit message!")
                break
            try:
                engine.setProperty('voice', voices[comment.voiceID].id)
            except:
                engine.setProperty('voice', voices[0].id)

            engine.say(comment.comment)
            engine.runAndWait()

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
        self.ballHistory = []
        self.lastTouches = []
        self.teams = []
        self.joinTimer = 0
        self.q = Queue(maxsize=3)
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

    def speak(self, phrase):
        if not self.q.full():
            self.q.put(Comment(phrase, random.randint(0, 1)))

    def timeCheck(self, newTime):
        if newTime - self.currentTime < -1:
            return True
        self.currentTime = newTime
        return False

    def overtimeCheck(self,packet):
        if not self.overTime:
            if packet.game_info.is_overtime:
                self.overTime = True
                self.speak(f"That's the end of regulation time, we're headed into over time with the score tied at {packet.teams[0].score}!")

    def gameWrapUp(self):
        if self.teams[0].score > self.teams[1].score:
            winner = "Blue"
        else:
            winner = "Orange"

        if abs(self.teams[0].score - self.teams[1].score) >=4:
            self.speak(f"Team {winner} has won today's match with a dominant performance.")
            #impressive victory
        else:
            #normal win message
            self.speak(f"Team {winner} clinched the victory this match")

        self.speak("Thank you all for watching today's game and never forget that Diablo is coming for you. G G everyone.")

    def stopHost(self):
        while self.q.full():
            pass
        self.q.put("exit")

    def handleShotDetection(self):
        if self.shotDetection:
            if len(self.ballHistory) > 0:
                shot,goal = shotDetection(self.ballHistory[-1],1)
                if shot:
                    if not self.q.full():
                        if self.lastTouches[-1].team == goal:
                            self.speak(f"That's a potential own goal from {self.lastTouches[-1].player_name}.")
                        else:
                            self.speak(f"{self.lastTouches[-1].player_name} takes a shot at the enemy net!")
                    self.shotDetection = False




    def updateTouches(self, packet):
        contactNames = rstring(["hit","touch","contact"])

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
                if self.currentTime - self.touchTimer >=4:
                    if self.q.empty():
                        if len(self.ballHistory) >0:
                            _ballHeading = ballHeading(self.ballHistory[-1])
                            if _ballHeading == 0:
                                if touch.team == 0:
                                    if self.ballHistory[-1].location[1] >= 0:
                                        self.speak(
                                            f"{touch.player_name}'s {contactNames} pushes the ball back towards blue")
                                    else:
                                        self.speak(
                                            f"{touch.player_name}'s {contactNames} moves the ball towards its own goal.")
                                else:
                                    if touch.team == 1:
                                        if self.ballHistory[-1].location[1] <= 0:
                                            self.speak(
                                                f"{touch.player_name}'s {contactNames} puts the ball into a dangerous position for blue.")
                                        else:
                                            self.speak(
                                                f"{touch.player_name}'s {contactNames} sends the ball towards blue side.")

                            elif _ballHeading == 1:
                                if touch.team == 0:
                                    if self.ballHistory[-1].location[1] >= 0:
                                        self.speak(
                                            f"{touch.player_name}'s {contactNames} puts the ball into a dangerous position for orange.")
                                    else:
                                        self.speak(
                                            f"{touch.player_name}'s {contactNames} sends the ball towards orange side.")
                                else:
                                    if touch.team == 1:
                                        if self.ballHistory[-1].location[1] >= 0:
                                            self.speak(
                                                f"{touch.player_name}'s {contactNames} moves the ball towards its own goal.")
                                        else:
                                            self.speak(
                                                f"{touch.player_name}'s {contactNames} pushes the ball back  towards orange")

                            else:
                                self.speak(f"{touch.player_name}'s {contactNames} is neutral.")

                            self.touchTimer = self.currentTime


    def updateGameBall(self,packet):
        if packet.game_info.is_round_active:
            currentBall = ballObject(packet.game_ball)
            self.ballHistory.append(currentBall)
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
            f"We have an exciting match in store for you today. On team blue We have {', '.join([x.name for x in self.teams[0].members])} ")
        self.speak(
            f" and facing off against them on orange team we have {', '.join([x.name for x in self.teams[1].members])} .")
        self.speak("Good luck everyone.")

    def scoreAnnouncement(self,teamIndex):
        try:
            scorer = self.teams[teamIndex].lastTouch.player_name
            speed = self.ballHistory[-1].getRealSpeed()
            if not self.q.full():
                if speed <= 20:
                    self.speak(f"{scorer} scores! It barely limped across the goal line at {speed} kilometers per hour, but a goal is a goal.")

                elif speed >= 100:
                    self.speak(f"{scorer} scores on a blazingly fast shot at  {speed} kilometers per hour! What a shot!")

                else:
                    self.speak(f"And {scorer}'s shot goes in at {speed} kilometers per hour!")

            if not self.q.full():
                self.speak(f"That goal brings the score to {self.teams[0].score} blue and {self.teams[1].score} orange.")
        except:
            pass

    def scoreCheck(self, packet):
        if self.teams[0].score != packet.teams[0].score:
            self.teams[0].score = packet.teams[0].score
            self.scoreAnnouncement(0)

        if self.teams[1].score != packet.teams[1].score:
            self.teams[1].score = packet.teams[1].score
            self.scoreAnnouncement(1)

    def main(self):
        while True:
            packet = GameTickPacket()
            self.game_interface.update_live_data_packet(packet)
            gametime = "{:.2f}".format(packet.game_info.seconds_elapsed)

            if packet.game_info.is_match_ended:
                print("Game is over, exiting.")
                self.gameWrapUp()
                self.stopHost()
                break

            if self.firstIter:
                if packet.num_cars >= 1:
                    if self.joinTimer <= 0:
                        self.joinTimer = time.time()
                    if time.time() - self.joinTimer >=1: #arbitrary timer to ensure all cars connected
                        self.firstIter = False
                        self.currentTime = float(gametime)
                        self.gatherMatchData(packet)

            if self.timeCheck(float(gametime)):
                print("framework reset, resetting announcerbot")
                self.reset()
            if not self.firstIter:
                self.updateGameBall(packet)
                self.updateTouches(packet)
                self.handleShotDetection()
                self.scoreCheck(packet)
                self.overtimeCheck(packet)


if __name__ == "__main__":
    s = Commentator()
    print("Exited commentator class")
