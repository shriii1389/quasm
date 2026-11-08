# name: the 8-deep limit applies to skipped text as well
# expect_error: Conditionals nested more than 8 deep
set c = 1
if c == 0
if c == 0
if c == 0
if c == 0
if c == 0
if c == 0
if c == 0
if c == 0
if c == 0
endif
endif
endif
endif
endif
endif
endif
endif
endif
end
