from .file1 import MY_CONSTANT1, MY_CONSTANT2, Vehicle, helper_function

class Engine:
    def __init__(self, type):
        self.type = type

    def get_identifier(self):
        return "4AGE" #Engine model

    def start_engine(self):
        return f"Engine ({self.type}) is starting."

class Car(Vehicle):
    def __init__(self, name, engine_type):
        super().__init__(name)
        self.engine = Engine(engine_type)

    def get_identifier(self):
        return "BQM532"; #Licence plate

    def drive(self):
        start_message = self.start()
        engine_message = self.engine.start_engine()
        helper_message = helper_function()
        licence_plate = self.get_identifier()
        test_const = MY_CONSTANT1
        return f"{start_message} | {engine_message} | {licence_plate} | Using helper: {helper_message} | Constant 1: {test_const} | Constant 1: {MY_CONSTANT2}"
