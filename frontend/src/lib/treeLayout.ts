import type { Schemas } from '@/lib/api'

type Tree = Schemas['FamilyTree']
type Person = Schemas['Person']

export const NODE = 64
const CELL_W = 96
const ROW_H = 124
const PAD = 28
/** Space under each circle for the name label, so connectors start below it. */
const LABEL_H = 26

export type PlacedPerson = { id: string; name: string; x: number; y: number }
export type Connector = { key: string; d: string }
export type TreeLayout = {
  nodes: PlacedPerson[]
  connectors: Connector[]
  width: number
  height: number
  /** People added by name with no relationship yet; listed beside the tree, not in it. */
  unplaced: Person[]
}

/**
 * Generations come from parent edges ("a is parent of b" puts a one row above b); spouses and
 * siblings share a row. Rows are ordered by their parents' positions and keep spouses together.
 */
export function layoutTree(tree: Tree): TreeLayout {
  const edges = tree.relationships
  const linked = new Set(edges.flatMap((e) => [e.a, e.b]))
  const gen = new Map<string, number>()
  const seen: string[] = []

  const roots = [tree.me, ...tree.people.map((p) => p.id)].filter(
    (id): id is string => !!id && (id === tree.me || linked.has(id)),
  )
  for (const root of roots) {
    if (gen.has(root)) continue
    gen.set(root, 0)
    const queue = [root]
    while (queue.length) {
      const id = queue.shift()!
      seen.push(id)
      for (const e of edges) {
        if (e.a !== id && e.b !== id) continue
        const other = e.a === id ? e.b : e.a
        if (gen.has(other)) continue
        const g = gen.get(id)!
        gen.set(other, e.kind === 'parent' ? g + (e.a === id ? 1 : -1) : g)
        queue.push(other)
      }
    }
  }

  const spousesOf = (id: string) =>
    edges.filter((e) => e.kind === 'spouse' && (e.a === id || e.b === id)).map((e) => (e.a === id ? e.b : e.a))
  const parentsOf = (id: string) => edges.filter((e) => e.kind === 'parent' && e.b === id).map((e) => e.a)

  const withSpouses = (ids: string[]) => {
    const out: string[] = []
    for (const id of ids) {
      if (out.includes(id)) continue
      out.push(id)
      for (const s of spousesOf(id)) if (ids.includes(s) && !out.includes(s)) out.push(s)
    }
    return out
  }

  const gens = [...new Set(gen.values())].sort((a, b) => a - b)
  const rows = new Map<number, string[]>()
  const col = new Map<string, number>()
  for (const g of gens) {
    let row = withSpouses(seen.filter((id) => gen.get(id) === g))
    const key = (id: string, i: number) => {
      const ps = parentsOf(id).filter((p) => col.has(p))
      if (ps.length) return ps.reduce((sum, p) => sum + col.get(p)!, 0) / ps.length
      const partner = spousesOf(id).find((s) => parentsOf(s).some((p) => col.has(p)))
      if (partner) return key(partner, i)
      return i - row.length / 2
    }
    row = withSpouses(
      row
        .map((id, i) => ({ id, k: key(id, i) }))
        .sort((a, b) => a.k - b.k)
        .map((r) => r.id),
    )
    row.forEach((id, i) => col.set(id, i - (row.length - 1) / 2))
    rows.set(g, row)
  }

  const widest = Math.max(1, ...[...rows.values()].map((r) => r.length))
  const width = PAD * 2 + widest * CELL_W
  const height = PAD * 2 + Math.max(1, gens.length) * ROW_H - (ROW_H - NODE - 30)
  const names = new Map(tree.people.map((p) => [p.id, p.display_name]))
  const pos = new Map<string, { x: number; y: number }>()
  const nodes: PlacedPerson[] = []
  gens.forEach((g, rowIndex) => {
    for (const id of rows.get(g)!) {
      const x = width / 2 + col.get(id)! * CELL_W
      const y = PAD + rowIndex * ROW_H + NODE / 2
      pos.set(id, { x, y })
      nodes.push({ id, name: names.get(id) ?? '', x, y })
    }
  })

  const r = NODE / 2
  const connectors: Connector[] = []
  for (const e of edges) {
    const a = pos.get(e.a)
    const b = pos.get(e.b)
    if (!a || !b || e.kind === 'parent') continue
    const [left, right] = a.x <= b.x ? [a, b] : [b, a]
    if (e.kind === 'spouse') {
      connectors.push({ key: `s-${e.a}-${e.b}`, d: `M${left.x + r} ${left.y}H${right.x - r}` })
    } else {
      const shared = parentsOf(e.a).some((p) => parentsOf(e.b).includes(p))
      if (shared) continue
      const top = left.y - r - 14
      connectors.push({
        key: `b-${e.a}-${e.b}`,
        d: `M${left.x} ${left.y - r}V${top}H${right.x}V${right.y - r}`,
      })
    }
  }
  for (const child of nodes) {
    const ids = parentsOf(child.id).filter((p) => pos.has(p))
    if (!ids.length) continue
    const parents = ids.map((p) => pos.get(p)!)
    const c = pos.get(child.id)!
    const midY = c.y - r - 26
    const couple =
      ids.length === 2 &&
      spousesOf(ids[0]).includes(ids[1]) &&
      Math.abs(parents[0].y - parents[1].y) < 1
    const starts = couple
      ? [{ x: (parents[0].x + parents[1].x) / 2, y: parents[0].y }]
      : parents.map((p) => ({ x: p.x, y: p.y + r + LABEL_H }))
    starts.forEach((s, i) =>
      connectors.push({ key: `p-${child.id}-${i}`, d: `M${s.x} ${s.y}V${midY}H${c.x}V${c.y - r}` }),
    )
  }

  return {
    nodes,
    connectors,
    width,
    height,
    unplaced: tree.people.filter((p) => !gen.has(p.id)),
  }
}
