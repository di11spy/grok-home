# grok-home

Private home for Dylan's Home Assistant custom work.

The first integration is **CL6 Remote Start**. It talks to the MyCarControls / CL6 cloud service so Home Assistant can see the car and, with a confirmation step, start it or unlock it.

## What you can do

- See whether the car is online, whether the engine is running, battery voltage, signal, and the last GPS position.
- Lock the doors, or stop the engine, right away.
- Arm a remote start or an unlock, then confirm it within a short window. Until you confirm, nothing is sent to the car.
- Let Home Assistant send one stop when the remote start has run long enough, or right away if the car reports speed above 0 during that remote start.
- On a cold day, optionally start the car one more time when the first run ends.

Staying signed in on your phone at the same time is fine. This integration is just another login.

## Install with HACS

HACS is the Home Assistant add-on store. Use it so updates are a button instead of a copy-paste.

1. Install HACS if it is not already installed: [hacs.xyz](https://hacs.xyz/).
2. This repository is private, so HACS needs a GitHub token that can read it.
   - On GitHub, open Settings → Developer settings → Personal access tokens.
   - Create a classic token with the **repo** scope, or a fine-grained token that can read `di11spy/grok-home`.
   - In Home Assistant, open Settings → Devices & services → HACS → Configure, and paste the token into the GitHub token field.
3. Open HACS, choose the three-dot menu, then **Custom repositories**.
4. Repository: `https://github.com/di11spy/grok-home`
5. Category: **Integration**. Add it.
6. In HACS, search for **CL6 Remote Start**, download it, and restart Home Assistant.

### If you are not using HACS

Copy the folder `custom_components/cl6` into your Home Assistant config folder, so the path is `config/custom_components/cl6`. Restart Home Assistant.

## Add the car

1. Settings → Devices & services → **Add integration**.
2. Search for **CL6 Remote Start**.
3. Enter the email and password from the MyCarControls app.
4. If the account has more than one car, pick the one you want.

The password is saved in Home Assistant's config entry for this integration. It is not written into this repository and the integration does not put it in the log.

To change the password later, wait for Home Assistant to ask you to reconnect, or remove the integration and add it again. The email cannot be edited in place. If you change email addresses, remove the integration and add it again.

## The controls

Open the CL6 device. You should see:

| Control | What it does |
| --- | --- |
| Remote start | Arms a start. Does not start the car. |
| Confirm | Sends the armed start or unlock. |
| Remote stop | Stops the engine immediately. |
| Door lock | Lock sends immediately. The first unlock tap only arms an unlock. |
| Engine, Ignition, Lock status, Online | On/off readings from the car. |
| Battery voltage, Signal, Last GPS time | Numbers and the last time CL6 reported a position. |
| Last command | Diagnostic. Shows the last action and whether it was success, failed, or unknown. |
| Location | The car on the map, when CL6 has a real GPS fix. |

CL6's door status is the lock, not whether a door is ajar. On this car it sends `locked` or `unlocked`. The Door lock control and Lock status use that same reading. Lock status is off when the car says locked, and on when it says unlocked. There is no separate open-or-closed door sensor.

Signal is the `Rssi` number CL6 sends. On this car it is a level such as 84, shown as a percentage. It is not a dBm signal strength.

Each of these sensors keeps the value CL6 sent in its `raw` attribute, including `true` and `false`. If a reading looks wrong, open the entity and look at `raw`.

## Confirmation

Remote start and unlock always take two steps. Stop and lock do not.

1. Press **Remote start**, or tap unlock on the door lock, or say "start her car".
2. Within 30 seconds (the default), press **Confirm**, or say "confirm".

A notification appears while it is armed. The arm expires. It can be used once. Confirming again does nothing until you arm again. Arming again starts a fresh window and throws away the previous arm.

You can also do it from Developer tools → Actions (older Home Assistant versions call this Services):

1. **CL6: Arm**, action `start` or `unlock`.
2. **CL6: Confirm**.

If more than one CL6 car is set up, pick the device in the target field.

Voice phrases, for Home Assistant's built-in Assist agent:

- "start her car", "start the car", "remote start the car" — arm a start, then Assist asks you to say confirm.
- "unlock the car" — arm an unlock.
- "confirm" — send it.
- "stop the car" and "lock the car" — happen immediately.

The integration copies those phrases to `config/custom_sentences/en/cl6.yaml` the first time it starts. You can edit the phrases. If you delete the first line (`# cl6-managed-sentences`), later updates will leave your file alone.

These phrases are for the built-in Home Assistant conversation agent. The Confirm button works even if a voice assistant is set to an external AI only.

A command usually takes about 20 seconds, because CL6 is polled twice before the result is known. Home Assistant stays responsive while it waits.

## Options

Settings → Devices & services → CL6 Remote Start → Configure.

- **Status refresh.** Default 5 minutes. Shortest is 2 minutes. This service is unofficial, so the integration does not poll faster than that.
- **Longest remote start.** Default 10 minutes. When that time is up, one engine stop is sent.
- **Cold day.** Off by default. When it is on, the end of the first run sends a second start instead of a stop, then one stop after another full run. With the default 10 minutes, that is about 20 minutes total. It does not ask you to confirm the second start.
- **Confirmation window.** Default 30 seconds. Shortest is 10 seconds.

Saving options does not cancel a remote start that is already counting down. That start keeps the timer it began with. Avoid changing options in the middle of a remote start.

## Automatic stop

This only applies to a remote start that **this integration** began.

- When the run time ends, it sends one stop.
- If CL6 reports speed above 0 during that run, it sends one stop right away and does not do the cold-day second start.
- It does not stop the engine just because you are driving with the key. There is no remote-start session in that case.
- A stop from the Remote stop button also cancels the timer, so it will not send a second stop by itself.

If Home Assistant restarts during a remote start, the timer is forgotten. The car's own remote-start timer should still shut the engine off. Press Remote stop if you want to be sure.

There is no garage-door check. The parking spot is an open carport today. When it becomes a climate-controlled garage, a "doors must be open" guard can be added. It is not in this version.

## When a command says unknown

CL6 sometimes does not answer before the wait is over. The result is then **unknown**, not failed. The command might still be on its way to the car.

The integration does not send that command again. On a later refresh it checks the old command id, and Last command updates if CL6 eventually says success or failed.

If a start comes back unknown, look at the car before you arm another start. If the engine is still off after the next refresh or two, you can arm and confirm again yourself.

## Logs

Every arm, expiry, send, and later result is written to the Home Assistant log and to Logbook, with the time, where it came from (dashboard, voice, timer, and so on), and the result. The log line does not include the password, the email, or the raw reply from CL6.

If you turn on debug logging, do not turn it on for `requests` or `urllib3`. Those libraries can print the login header.

## First time on the real car

The library this uses has not had its live vehicle commands verified by its author. Try the safe order, with the car parked in the carport, in Park, and with nobody in it.

1. Confirm the MyCarControls app can still see the car.
2. Add the integration and check that Online, voltage, and location look sensible. Glance at each sensor's `raw` attribute.
3. Lock the doors. They should lock, and the log should say success.
4. Tap unlock, then Confirm. The doors should unlock.
5. Press Remote start, then Confirm. Wait for Last command to leave "unknown" if it lands there. The Engine sensor should turn on if CL6 reports it.
6. Press Remote stop.
7. Only after that, try a timed start and let it reach the automatic stop while you are standing next to the car.
8. Do not test the speed stop by driving until you trust the start and stop. A GPS speed glitch above 0 during a remote start will send one stop.

## Limitations

- Unofficial API. It can change or stop without notice.
- No two-factor login and no refresh token. If the password changes, Home Assistant asks for the new one.
- A timed-out command is unknown. It is never retried automatically.
- Status is polled, at best every 2 minutes, plus one refresh after each command. It is not instant.
- Door status from CL6 is locked or unlocked. The integration does not know if a door is physically open.
- Signal is shown as a percentage because the live `Rssi` value is a 0–100 style level, not dBm.
- Engine and ignition words are still best guesses. Check the `raw` attribute if one looks wrong.
- Voice confirm uses the word "confirm". If that gets in the way of another phrase, edit `config/custom_sentences/en/cl6.yaml`.
- The car's own module may also shut the engine off on its own schedule. This integration still sends its own stop.

## Development

Tests mock the CL6 client and do not call the live service.

```sh
python -m pip install -r requirements-test.txt
python -m ruff check .
python -m pytest
```

PyCarLink is included under `custom_components/cl6/vendor/pycarlink/` from [angel12/PyCarLink](https://github.com/angel12/PyCarLink) at commit `a11d551491fc8e6025c7d68314cc7666d040cbac`. It stays MIT licensed. See `VENDOR.md` there for the local changes: choose a vehicle by id, and submit a command without blocking for 20 seconds.
