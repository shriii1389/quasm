# name: a tab is whitespace wherever a space is
qubit	q[2]
qubitop1	q[0]	=	H
qubitop2	q[0],	q[1]	=	CN
set	c	=	0
if	c	==	0
	print(q)
endif
end
