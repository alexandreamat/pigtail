"""Domain models, one file per area: box, device, conductor, cable, circuit, house.

The pydantic models are the YAML schema and the working objects; via ``.part`` /
``.bus`` they also project themselves into SKiDL. Import from the submodules
directly, e.g. ``from pigtail.models.house import House``.
"""
