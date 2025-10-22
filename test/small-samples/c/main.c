/*
 * C Language Test Sample - Main Implementation File
 * Demonstrates include relationships and function calls
 */

#include "../shlib/utils.h"
#include <stdio.h>

// Global variable with external linkage
int global_counter = 0;

int main() {
    // Function calls to utils.h functions
    print_hello();
    int result = add_numbers(5, 3);
    double avg = calculate_average(10.0, 20.0, 30.0);

    // Variable usage - referencing global variable
    global_counter++;

    printf("Result: %d, Average: %.2f, Counter: %d\n",
           result, avg, global_counter);

    return 0;
}

void process_data() {
    // Another function call from main.c
    int value = multiply_numbers(4, 7);
    printf("Multiplied result: %d\n", value);
}
