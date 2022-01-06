import time

class SequenceTracker:
    def __init__(self, memory_time=10):
        self.sequence_storage = []
        self.recents = []
        self.memory_time = memory_time # s

    def remember(self, sequence):
        t = time.time()
        self.sequence_storage.append((sequence, t))
        self.recents.append(sequence)

    def update_recents(self):
        now = time.time()
        for sequence, t_recorded in self.sequence_storage:
            if now - t_recorded > self.memory_time:
                self.sequence_storage.remove((sequence, t_recorded))
                self.recents.remove(sequence)