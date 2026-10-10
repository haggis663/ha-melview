# HomeAssistant - MelView

HomeAssistant component for mitsubishi air conditioner (MelView) for Australia and pehaps New Zealand
It handles climate control as well as zone control

## Sensors

Some units report more than the climate entity shows. Where a unit reports
them, these are added as sensors:

| Sensor | Status field | Units that report it |
|---|---|---|
| Outdoor temperature | `outdoortemp` | Lossnay (air at the outdoor intake), and any other unit that reports it |
| Supply air temperature | `supplytemp` | Lossnay |
| Exhaust air temperature | `exhausttemp` | Lossnay |
| Core efficiency | `coreefficiency` | Lossnay |
| Filter (problem sensor) | `changefilter` | Lossnay |

They read the status the climate entity already fetches, so they add no
requests to MelView. A sensor is only created if the unit reported its field
when the integration started.


## Alternatives with more functionality

Unfortunately, I've had very little time to focus on this, so it's stagnated with a few things to do.
Currently it lacks `async` support, plus zones and dynanamic fan speeds are only in the `dev` branch.

There is a fork - https://github.com/haggis663/ha-melview - which has this plus releases to HACS, so that's probably the best replacement for anyone who needs more functionality.

I do hope to work on this again in the future, but I have no idea when...

## Installing

- Clone the required parts of the repo to <config_dir>/custom_components/melview/ or use HACS (add custom repository)

Restart home assistant, refresh browser cache and add integration melview


## License

This project is licensed under the WTF License
