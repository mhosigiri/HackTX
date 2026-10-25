-- Each object's lasting features as one line of text, written when its photo is read, so a new
-- capture is compared against saved objects with one indexed query and a short prompt.
alter table heirloom add column signature text;
alter table heirloom add column signature_terms tsvector
  generated always as (to_tsvector('english'::regconfig, coalesce(signature, ''))) stored;
create index heirloom_signature_terms on heirloom using gin (signature_terms);

-- Objects read before this: what the photo showed, until the next read writes a proper one.
update heirloom h set signature = concat_ws('; ', h.category, d.details)
from (
  select heirloom_id, string_agg(text, '; ' order by confidence desc nulls last) as details
  from fact where kind = 'observation' and source->>'via' = 'vision'
  group by heirloom_id
) d
where d.heirloom_id = h.id;
