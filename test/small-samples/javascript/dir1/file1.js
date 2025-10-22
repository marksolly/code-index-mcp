export const MY_CONSTANT = "A_CONSTANT_STRING";

export function helper_function() {
    return "I am a helper function";
}

export class Vehicle {
    constructor(name) {
        this.name = name;
    }

    start() {
        return `${this.name} is starting.`;
    }
}

export const vehiclePolisher = () => {
    return "The paint looks immaculate!";
};

export function test_caller() {
    return helper_function();
}
