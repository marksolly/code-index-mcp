/*
 * C Language Test Sample - Header File
 * Demonstrates function declarations, global variables, and preprocessor ambiguity
 */

#ifndef UTILS_H
#define UTILS_H

// Function declarations
void print_hello();
int add_numbers(int a, int b);
double calculate_average(double a, double b, double c);
int multiply_numbers(int a, int b);

// Global variable declarations with external linkage
extern int global_counter;

// Platform-specific includes - demonstrates preprocessor ambiguity
// This creates REAL ambiguity that requires probabilistic relationships
#ifdef WINDOWS_PLATFORM
    #include "windows_platform.h"  // Provides HANDLE, DWORD types
#else
    #include "linux_platform.h"    // Provides int-based types
#endif

// Same typedef names, but different definitions based on included platform header
typedef HANDLE FileHandle;  // Ambiguous: void* (Windows) or int (Linux)?
typedef DWORD ErrorCode;    // Ambiguous: unsigned long (Windows) or int (Linux)?

// Functions using ambiguous typedefs - static analysis cannot determine types
FileHandle open_file(const char* path);
ErrorCode get_last_error();

#endif /* UTILS_H */
