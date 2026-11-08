# a single = is assignment, not a comparison
# expect_error: Syntax Error
set c = 1
if c = 1
endif
end
