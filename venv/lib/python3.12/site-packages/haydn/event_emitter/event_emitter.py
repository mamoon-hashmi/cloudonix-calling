__author__ = 'leemin'


class EventEmitter:
    listeners = {}

    def __init__(self):
        self.listeners = {}

    def on(self, event_name, listener):
        if event_name not in self.listeners:
            self.listeners[event_name] = []

        self.listeners[event_name].append(listener)
        return

    def off(self, event_name, listener):
        if event_name in self.listeners:
            self.listeners[event_name].remove(listener)

    def fire(self, event_name, *args):
        listeners = self.listeners.get(event_name)

        if listeners is not None:
            for listener in listeners:
                listener(*args)
