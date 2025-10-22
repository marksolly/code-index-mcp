import { MY_CONSTANT, Vehicle, helper_function, vehiclePolisher, test_caller } from '../dir1/file1.js';

const MAX_VEHICLE_SPEED = 200; // km/h - vehicle performance constant

class Engine {
    constructor(type) {
        this.type = type;
    }

    get_identifier(){
        return `4AGE`; //Engine model
    }

    start_engine() {
        return `Engine (${this.type}) is starting.`;
    }
}

export class Car extends Vehicle {
    constructor(name, engine_type) {
        super(name);
        this.engine = new Engine(engine_type);
    }

    get_identifier(){
        return `BQM532`; //Licence plate
    }

    drive() {
        const start_message = this.start();
        const engine_message = this.engine.start_engine();
        const helper_message = helper_function();
        const polish_message = vehiclePolisher();
        const licence_plate = this.get_identifier();
        return `${start_message} | ${engine_message} | ${licence_plate} | Using helper: ${helper_message} | Constant: ${MY_CONSTANT} | Max Speed: ${MAX_VEHICLE_SPEED} | Polish: ${polish_message}`;
    }
}
