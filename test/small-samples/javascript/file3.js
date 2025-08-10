import { Car } from './file2.js';

class Garage {
    constructor(name) {
        this.name = name;
        this.cars = [];
    }

    service_car(car_name, engine_type) {
        const car = new Car(car_name, engine_type);
        this.cars.push(car);
        // This demonstrates a method in one class calling a method in another class.
        return car.drive();
    }
}

function main() {
    const my_garage = new Garage("Mark's Garage");
    const result = my_garage.service_car("Tesla Model S", "Electric");
    console.log(result);
}

main();
