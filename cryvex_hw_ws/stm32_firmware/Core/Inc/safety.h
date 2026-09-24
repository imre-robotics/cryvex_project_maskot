/* Tampon switch (PA0) ve acil stop 2. kontagi (PA1) - basit polling, NC hat:
 * pin LOW = tetiklenmis (basilmis VEYA kablo kopmus - guvenli varsayilan). */
#ifndef SAFETY_H
#define SAFETY_H

#include "app_config.h"
#include <stdbool.h>

void safety_poll(void); /* her ana dongu turunda cagrilir */
bool safety_bumper_hit(void);
bool safety_estop_hit(void);

#endif /* SAFETY_H */
