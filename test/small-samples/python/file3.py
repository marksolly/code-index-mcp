from .file2 import Car

class Garage:
    def __init__(self, name):
        self.name = name
        self.cars = []

    def service_car(self, car_name, engine_type):
        car = Car(car_name, engine_type)
        self.cars.append(car)
        # This demonstrates a method in one class calling a method in another class.
        return car.drive()

def main():
    my_garage = Garage("Mark's Garage")
    result = my_garage.service_car("Tesla Model S", "Electric")
    print(result)

if __name__ == "__main__":
    main()
