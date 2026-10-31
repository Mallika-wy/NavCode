
Before selecting a ground dot, locate the route-relevant opening, passage or
approach direction in the CURRENT image. In the final JSON include
"route_anchor": {"description": "visible route feature and why it follows the instruction",
                 "coordinate_frame": "normalized_1000", "image_xy": [x, y]}
or null if no route direction is visible. Use a 0..1000 coordinate system:
left edge x=0, image center x=500, right edge x=1000. For example a left-side
opening may have image_xy=[200, 600]. Always state coordinate_frame explicitly.
Coordinates refer to the CURRENT image's top-left corner, not a historical
frame or crop. The anchor describes the desired route DIRECTION; it
is not a promise that the object, doorway center or pixel can be reached.
Find that feature independently of the yellow dots. A central dot on a rug is
not a route to a doorway at the image edge just because both are visible.
Only select a dot whose bearing points toward this route feature. If the
opening is left/right of every available dot, set target_candidate_id to null
and suggest LEFT/RIGHT to center that opening before taking a new local target.
Use recent depth/stall feedback to change the view or direction after a failed
approach. Do not keep choosing the nearest dot when it points toward furniture
or a wall. Report completion from evidence, independently of selecting motion.
When the predicate is SUPPORTED, route_anchor may be null.
