// Class joiner the Magic UI components import. ponytail: no tailwind-merge, so conflicting classes resolve by CSS order; add it if overrides misbehave.
export const cn = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')
