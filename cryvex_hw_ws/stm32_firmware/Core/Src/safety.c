#include "safety.h"
#include "main.h"

static bool s_bumper;
static bool s_estop;

void safety_poll(void)
{
    /* NC hat + pull-up: normalde HIGH (devre kapali/saglam). Herhangi bir
     * switch acilirsa VEYA kablo koparsa hat LOW olur - "tetiklendi" say. */
    s_bumper = (HAL_GPIO_ReadPin(BUMPER_GPIO_Port, BUMPER_Pin) == GPIO_PIN_RESET);
    s_estop  = (HAL_GPIO_ReadPin(ESTOP_SENSE_GPIO_Port, ESTOP_SENSE_Pin) == GPIO_PIN_RESET);
}

bool safety_bumper_hit(void) { return s_bumper; }
bool safety_estop_hit(void)  { return s_estop; }
