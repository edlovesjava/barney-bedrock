// Seed only: forces framework download at image build time.
#ifdef ARDUINO
#include <Arduino.h>
void setup() {}
void loop() {}
#else
int main() { return 0; }
#endif
