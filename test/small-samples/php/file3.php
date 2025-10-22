<?php

require_once './dir2/file2.php';

class Garage {
    public $name;
    public $loan_car;
    public $cars;

    public function __construct($name) {
        $this->name = $name;
        $this->loan_car = new Car("Loan Car", "Diesel");
        $this->cars = [];
    }

    public function service_car($car_name, $engine_type) {
        $car = new Car($car_name, $engine_type);
        $this->cars[] = $car;
        // This demonstrates a method in one class calling a method in another class.
        return $car->drive();
    }
}

function main() {
    $my_garage = new Garage("Mark's Garage");
    $result = $my_garage->service_car("Tesla Model S", "Electric");
    echo $result . "\n";
}

main();
