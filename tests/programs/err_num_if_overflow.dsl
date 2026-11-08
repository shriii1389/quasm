# name: a comparison literal past 2^32 is out of range
# expect_error: Number out of range
set c = 1
if c == 4294967297
endif
end
