# name: a second plain else is an error, not silently accepted
# expect_error: else after else
set c = 0
if c == 1
else
else
endif
end
