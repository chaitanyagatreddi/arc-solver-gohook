# GoHook, 3-day MVP: check the answer before someone acts on it

## Who pays $10 a month

- Reddit agencies. One bad reply can lose a client.
- Account warmers. One slip undoes months of warming.
- Reddit marketers. A removed post is a lost day of getting customers.
- Reddit ghostwriters. A wrong claim makes the client look careless.
- Content creators. A ban takes the audience they built.
- NSFW creators. They post in many places and often skip the rules. A ban takes the income.
- AI content creators. They publish a lot, fast. That is how a bad post gets out.

They pay every month because the check keeps running on new posts, new threads, and new competitor talk.

A founder sees the whole surface: where the brand shows up, and whether people are positive or negative. An NSFW creator sees rival accounts: karma, where they post, and which posts stay up. Both only see what is public.

## Cost of doing nothing

A founder uses GoHook, then posts, replies, or chases a competitor based on what GoHook said. If that answer was only true for the few threads it was written from, they act on a false picture.

What that costs:

- **Ghostwriting.** They post a reply that sounds sure and is wrong. The account looks spammy. One bad week can cost the audience they spent months building.
- **Social signals.** They spend the day on a thread that was an ad, or miss a person who was actually asking to buy. The cost is a wasted day, or a buyer who went to someone else.
- **Competitor intel.** They change price, copy, or a sales call because GoHook said “people hate X.” If that came from two threads, the decision is wrong. The cost is a wrong move in the market, not a wrong sentence.

Doing nothing keeps today’s behavior: GoHook writes the answer from the same threads it then treats as proof. The person cannot tell a solid answer from a guess. He pays $10 once for now. Later he pays $10 every month, because the check keeps running: new threads, new replies, new things said about competitors. An unchecked answer makes that monthly $10 feel wasted, and he cancels.

Three days of work is smaller than one wrong public post or one wrong pricing move.

## What we build

One check. Write the answer from most of the threads. Hold the rest back. Keep the answer only if those held-back threads still agree. If they do not, do not show it as ready.

If there are fewer than 5 threads, skip the check and show today’s answer.

## Three days

**Day 1. Done.** The check is in `src/gohook_arc/check.py`. It saves pass, fail, unclear, or skipped. Nobody sees a change.

**Day 2.** Run it on ghostwriting (a post or reply in their voice) and on competitor intel (their brand versus others: price, complaints, praise). Still show the old answer. Save whether it held up.

**Day 3.** Social signals: send a thread only when the reason is a real quote from that thread. Competitor intel: show one line, “this held up” or “held back,” with the quotes. Ghostwriting stays hidden until we see the check is not blocking good writing.

## Not in these 3 days

The ten safe subreddits. The BanAware “stop for today” line that is already written by hand. A new screen. A second search for more threads.
