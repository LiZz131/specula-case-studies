#ifndef SPECULA_STEP_H_
#define SPECULA_STEP_H_

#ifdef __cplusplus
extern "C" {
#endif

/* 0 keeps the library's own control flow.
 * The driver sets this to 1 for a whole controlled run, before any Raft call.
 * The gates below are the only places a spec action is split out of a
 * library call that does several spec actions at once. */
extern int specula_step;

#ifdef __cplusplus
}
#endif

#endif
