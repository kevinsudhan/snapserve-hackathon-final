import { create } from 'zustand'

export type Theme = 'dark' | 'light'

const KEY_THEME = 'araxysdesk.theme'
const KEY_RAIL = 'araxysdesk.rail'

function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY_THEME)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* storage may be blocked */
  }
  return 'dark'
}

function readRail(): boolean {
  try {
    return localStorage.getItem(KEY_RAIL) === '1'
  } catch {
    return false
  }
}

type UiState = {
  theme: Theme
  railCollapsed: boolean
  paletteOpen: boolean
  /**
   * Whether the navigation drawer is open on a narrow screen.
   *
   * Deliberately separate from `railCollapsed`, and deliberately not
   * persisted. Collapsing the rail is a preference about how you like the
   * desk laid out and should survive a reload; opening the drawer is a
   * gesture that lasts until you pick something. Storing the second one
   * would mean reopening the app to a menu covering the page.
   */
  navOpen: boolean
  setTheme: (t: Theme) => void
  toggleTheme: () => void
  toggleRail: () => void
  setNavOpen: (v: boolean) => void
  setPaletteOpen: (v: boolean) => void
}

export const useUi = create<UiState>((set, get) => ({
  theme: readTheme(),
  railCollapsed: readRail(),
  navOpen: false,
  paletteOpen: false,

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem(KEY_THEME, theme)
    } catch {
      /* ignore */
    }
    set({ theme })
  },

  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),

  toggleRail: () =>
    set((s) => {
      const railCollapsed = !s.railCollapsed
      try {
        localStorage.setItem(KEY_RAIL, railCollapsed ? '1' : '0')
      } catch {
        /* ignore */
      }
      return { railCollapsed }
    }),

  setNavOpen: (navOpen) => set({ navOpen }),

  setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
}))

/** apply the persisted theme before first paint */
export function bootTheme() {
  document.documentElement.setAttribute('data-theme', readTheme())
}
