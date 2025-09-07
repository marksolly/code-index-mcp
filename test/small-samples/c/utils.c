/*
 * C Language Test Sample - Implementation File
 * Demonstrates function definitions
 */

#include "utils.h"
#include <stdio.h>

// Global variable definition
int global_counter = 0;

// Function implementations
void print_hello() {
    printf("Hello from utils.c!\n");
}

int add_numbers(int a, int b) {
    return a + b;
}

double calculate_average(double a, double b, double c) {
    return (a + b + c) / 3.0;
}

int multiply_numbers(int a, int b) {
    return a * b;
}
