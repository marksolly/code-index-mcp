/*
 * C Language Test Samples - Type Usage Examples
 * Demonstrates actual usage of typedefs, structs, and enums
 */

#include "../shlib/types.h"
#include <stdio.h>

// Global variables using our types
Point_t global_point = {10, 20};
Color_t global_color = RED;
HttpStatus global_status = OK;

// Function parameters using our types
void print_point(Point_t p) {
    printf("Point: (%d, %d)\n", p.x, p.y);
}

void print_rectangle(Rectangle rect) {
    printf("Rectangle: top_left(%d,%d), bottom_right(%d,%d)\n",
           rect.top_left.x, rect.top_left.y,
           rect.bottom_right.x, rect.bottom_right.y);
}

void print_user(User_t* user) {
    printf("User: %s, age %d\n", user->name, user->age);
}

// Enum usage
void print_color(Color_t c) {
    switch(c) {
        case RED: printf("Red\n"); break;
        case GREEN: printf("Green\n"); break;
        case BLUE: printf("Blue\n"); break;
    }
}

void print_status(HttpStatus status) {
    printf("HTTP Status: %d\n", status);
}

// Typedef usage
Integer create_integer(int value) {
    return value;
}

void process_person(Person person) {
    printf("Person: %s %s\n", person.first, person.last);
}

// Struct instantiation and usage
int main() {
    Point_t p = {5, 10};
    print_point(p);

    Rectangle r = {
        .top_left = {0, 0},
        .bottom_right = {100, 50}
    };
    print_rectangle(r);

    User_t user = {
        .name = "Alice",
        .age = 30,
        .location = {25, 75}
    };
    print_user(&user);

    print_color(GREEN);
    print_status(NOT_FOUND);

    Integer num = create_integer(42);
    printf("Integer value: %d\n", num);

    Person person = {"John", "Doe"};
    process_person(person);

    return 0;
}
