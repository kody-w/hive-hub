# Customer-success operating material

SYNTHETIC business and ticket exercise. These are **unsent internal draft
patterns**, not correspondence with customers and not evidence of resolution.
Use synthetic ticket IDs only. There are no recipient addresses.

## Urgent export/retry class

Draft: “We are reviewing the reported export/retry behavior and the way urgent
items enter the work queue. The current internal candidate is under testing.
We have not yet confirmed that it resolves your reported issue. Our next
review will separate queue-priority changes from the underlying export
behavior, and we will only communicate a resolution after it is verified.”

Review note: a scheduler fix does not repair every export bug. Do not imply a
deployment, recovery of lost data, refund, resolution date, or financial result.
An owner must approve any actual message and any commitments.

## Blocked reproduction class

Draft: “The available reproduction is incomplete. We are keeping the issue
visible rather than marking it resolved. The next step is to identify the
minimum safe reproduction information needed; no sensitive information should
be sent through an unapproved channel.”

Review note: the supplied ticket is synthetic. A real request for information
would need a separate approved data-collection purpose and channel.

## Low-priority readability class

Draft: “The readability feedback is recorded for review. It is not in the
current urgent recovery slice, and we are not promising a completion date.
We will reassess it after the bounded recovery review.”

## Routing and evidence

Product recovery reviews technical accuracy. Operations checks whether the
work is only planned, actually started, or verified. Finance reviews any
money-related statement. Customer success preserves uncertainty and drafts
the message. The owner separately approves sending. Keep each unresolved
ticket in the backlog and distinguish response preparation from resolution.
