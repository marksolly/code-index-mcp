from .file1 import MY_CONSTANT, Vehicle, helper_function

class Engine:
    def __init__(self, type):
        self.type = type

    def start_engine(self):
        return f"Engine ({self.type}) is starting."

class Car(Vehicle):
    def __init__(self, name, engine_type):
        super().__init__(name)
        self.engine = Engine(engine_type)

    def drive(self):
        start_message = self.start()
        engine_message = self.engine.start_engine()
        helper_message = helper_function()
        return f"{start_message} | {engine_message} | Using helper: {helper_message} | Constant: {MY_CONSTANT}"
