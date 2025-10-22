<?php

const MY_CONSTANT1 = "A_CONSTANT_STRING";
define("MY_CONSTANT2", "ANOTHER_CONSTANT_STRING");

function helper_function() {
    return "I am a helper function";
}

class Vehicle {
    public $name;

    public function __construct($name) {
        $this->name = $name;
    }

    public function start() {
        return $this->name . " is starting.";
    }
}

function vehiclePolisher() {
    return "The paint looks immaculate!";
}
