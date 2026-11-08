# name: so is an else if after the plain else
# expect_error: else after else
set c = 0
if c == 1
else
else if c == 0
endif
end
