#include "safety.h"
#include "main.h"

static bool s_bumper;
static bool s_estop;

void safety_poll(void)
{
    /* NC anahtar zinciri PIN ILE GND ARASINA baglanir + dahili pull-up:
     * saglam ve basilmamisken zincir pini GND'ye ceker (LOW). Herhangi bir
     * anahtar acilirsa VEYA kablo koparsa (ya da hic bagli degilse) pull-up
     * hatti HIGH yapar -> "tetiklendi" (guvenli taraf).
     * 2026-09-26 duzeltmesi: once LOW=tetiklendi yaziliydi - pull-up ile
     * kopan kablo HIGH okunur, yani kopukluk ASLA algilanmazdi (hicbir sey
     * bagli degilken bile "sorun yok" diyordu). */
    s_bumper = (HAL_GPIO_ReadPin(BUMPER_GPIO_Port, BUMPER_Pin) == GPIO_PIN_SET);
    s_estop  = (HAL_GPIO_ReadPin(ESTOP_SENSE_GPIO_Port, ESTOP_SENSE_Pin) == GPIO_PIN_SET);
}

bool safety_bumper_hit(void) { return s_bumper; }
bool safety_estop_hit(void)  { return s_estop; }
