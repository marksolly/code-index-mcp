/*
 * C Language Test Samples - Type Definitions
 * Demonstrates struct, typedef, and enum support
 */

#ifndef TYPES_H
#define TYPES_H

// Struct definitions (base types)
struct Point {
    int x;
    int y;
};

struct Rectangle {
    struct Point top_left;
    struct Point bottom_right;
};

struct User {
    char* name;
    int age;
    struct Point location;
};

// Enum definitions (base types)
enum Color {
    RED,
    GREEN,
    BLUE
};

enum Status {
    OK = 200,
    NOT_FOUND = 404,
    INTERNAL_ERROR = 500
};

// Typedef examples with different names (no conflicts)
// These test the smart filtering logic
typedef int Integer;                    // Primitive alias (should be filtered)
typedef struct Point Point_t;           // Struct alias (should be tracked)
typedef struct User User_t;             // Struct alias (should be tracked)
typedef enum Color Color_t;             // Enum alias (should be tracked)
typedef enum Status HttpStatus;         // Enum alias (should be tracked)

// Anonymous struct typedef (should be tracked)
typedef struct {
    char* first;
    char* last;
} Person;

#endif /* TYPES_H */
