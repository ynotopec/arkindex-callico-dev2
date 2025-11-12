import { assign, merge } from 'lodash'
import { DISPLAY_MODE, SELECT_MODE, ELEMENT_MODES } from '../config'
import * as api from '../api'

export const initialState = () => ({
  /*
   * Elements retrieved from the Rest API of the Callico application
   * which allows to retrieve the details of the elements without using props.
   * { [id]: element }
   */
  elements: {},
  mode: DISPLAY_MODE,
  // Current ID of the selected elements
  selected: [],
  // Current ID of the highlighted elements
  highlighted: [],
  // Current ID of the hovered element
  hovered: null
})

export const mutations = {
  set (state, element) {
    state.elements = {
      ...state.elements,
      [element.id]: { ...merge(state.elements[element.id] || {}, element) }
    }
  },

  setMode (state, mode) {
    state.mode = mode
  },

  setSelected (state, { ids, force = false }) {
    // Select element only in select mode
    if (!force && state.mode !== SELECT_MODE && ids.length) return
    state.selected = [...ids]
  },

  addSelected (state, { id, force = false }) {
    // Select element only in select mode
    if (state.selected.includes(id) || (!force && state.mode !== SELECT_MODE)) return

    state.selected = [...state.selected, id]

    // Send notification to the application
    document.dispatchEvent(new CustomEvent('select-element', { detail: id }))
  },

  removeSelected (state, { id, force = false }) {
    // Unselect element only in select mode
    if (!state.selected.includes(id) || (!force && state.mode !== SELECT_MODE)) return

    const ids = state.selected
    ids.splice(ids.indexOf(id), 1)
    state.selected = [...ids]

    // Send notification to the application
    document.dispatchEvent(new CustomEvent('unselect-element', { detail: id }))
  },

  setHighlighted (state, { ids }) {
    state.highlighted = [...ids]
  },

  setHovered (state, id) {
    state.hovered = id
  },

  reset (state) {
    assign(state, initialState())
  }
}

export const actions = {
  async get ({ commit }, id) {
    const element = await api.retrieveElement(id)
    commit('set', element)
  },

  setMode ({ commit }, mode) {
    if (!ELEMENT_MODES.includes(mode)) return

    commit('setMode', mode)
    commit('setSelected', { ids: [] })
    commit('setHighlighted', { ids: [] })
    commit('setHovered', '')
  }
}

export default {
  namespaced: true,
  state: initialState(),
  mutations,
  actions
}
