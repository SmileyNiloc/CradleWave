#include <stdio.h>
#include <stdint.h>
#define BGT60_NUM_CHIRPS 32
#define BGT60_NUM_SAMPLES 64
#define BGT60_TOTAL_SAMPLES (BGT60_NUM_CHIRPS * BGT60_NUM_SAMPLES)
#define BGT60_FRAME_BYTES (BGT60_TOTAL_SAMPLES * sizeof(uint16_t))
int main() { printf("%d\n", (int)BGT60_FRAME_BYTES); }
