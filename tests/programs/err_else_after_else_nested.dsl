# name: ...and inside an if that is itself being skipped
# expect_error: else after else
set c = 0
if c == 1
if c == 2
else
else
endif
endif
end
