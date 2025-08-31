<?php

require_once 'file1.php';

class Engine {
    public $type;

    public function __construct($type) {
        $this->type = $type;
    }

    public function get_identifier() {
        return "4AGE"; // Engine model
    }

    public function start_engine() {
        return "Engine (" . $this->type . ") is starting.";
    }
}

class Car extends Vehicle {
    public $engine;

    public function __construct($name, $engine_type) {
        parent::__construct($name);
        $this->engine = new Engine($engine_type);
    }

    public function get_identifier() {
        return "BQM532"; // Licence plate
    }

    public function drive() {
        $start_message = $this->start();
        $engine_message = $this->engine->start_engine();
        $helper_message = helper_function();
        $polish_message = vehiclePolisher();
        $licence_plate = $this->get_identifier();
        $test_const1 = MY_CONSTANT1;
        return $start_message . " | " . $engine_message . " | " . $licence_plate . " | Using helper: " . $helper_message . " | Constant 1: " . $test_const1 . " | Constant 2: " . MY_CONSTANT2 . " | Polish: " . $polish_message;
    }
}
