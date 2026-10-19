class Clock:
    def __init__(self,now=1700000000):
        self.wall=float(now)
        self.active=0.0
    def time(self): return self.wall
    def monotonic(self): return self.active
    def sleep(self,seconds):
        self.wall+=seconds; self.active+=seconds
