import time

class SequenceTracker:
    def __init__(self, memory_time=20):
        self.sequence_storage = []
        self.counter = {}
        self.recents = []
        self.memory_time = memory_time # s
        self.ban_time = 60 # s

    def remember(self, sequence):
        t = time.time()
        self.sequence_storage.append((sequence, t))
        self.recents.append(sequence)
        
        if sequence in self.counter:
            self.counter[sequence] += 1
        else:
            self.counter[sequence] = 1

    def update_recents(self):
        now = time.time()
        for sequence, t_recorded in self.sequence_storage:
            if sequence in self.counter:
                multiplier = self.counter[sequence]
            else:
                multiplier = 1

            if now - t_recorded > self.memory_time*multiplier:
                self.sequence_storage.remove((sequence, t_recorded))
                self.recents.remove(sequence)
