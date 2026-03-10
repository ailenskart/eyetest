from interactive_session import InteractiveSession

session = InteractiveSession(base_url="http://dummy")
session.start_distance_vision()
session.process_response("Able to read with pinhole")

# Emulate sync-power
right = {"sph": -1.25, "cyl": 0.0, "axis": 180}
if 'sph' in right: session.current_row.r_sph = float(right['sph'])
if 'cyl' in right: session.current_row.r_cyl = float(right['cyl'])
if 'axis' in right: session.current_row.r_axis = float(right['axis'])

print("Before Blurry:", session.current_row.r_sph)
res = session.process_response("Blurry")
print("After Blurry:", session.current_row.r_sph)
print("Response Dict:", res['power']['right']['sph'])
