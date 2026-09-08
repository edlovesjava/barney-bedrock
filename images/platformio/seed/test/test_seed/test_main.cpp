#include <unity.h>
void setUp() {}
void tearDown() {}
void test_seed() { TEST_ASSERT_TRUE(true); }
int main(int, char**) { UNITY_BEGIN(); RUN_TEST(test_seed); return UNITY_END(); }
