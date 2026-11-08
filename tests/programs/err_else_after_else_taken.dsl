# name: ...and when the if's first branch ran, so the elses are being skipped
# expect_error: else after else
set c = 1
if c == 1
else
else
endif
end
