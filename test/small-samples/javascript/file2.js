import { MY_CONSTANT, Vehicle, helper_function } from './file1.js';

class Engine {
    constructor(type) {
        this.type = type;
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

    drive() {
        const start_message = this.start();
        const engine_message = this.engine.start_engine();
        const helper_message = helper_function();
        return `${start_message} | ${engine_message} | Using helper: ${helper_message} | Constant: ${MY_CONSTANT}`;
    }
}
