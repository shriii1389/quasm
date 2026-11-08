# name: 1e18 is out of range: its square could overflow float32 when summed
# expect_error: Number out of range
qubit a = [(1e18,0),(0,0)]
end
