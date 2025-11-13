const ELEMENT_TYPE_SELECTOR_ID = 'element-type-selector'
const LOCAL_STORAGE_ELEMENT_TYPE = 'elements-annotate-element-type'

export const getTypeOption = (typeId) => {
  return document.querySelector(`[type-id="${typeId}"]`)
}

export const initTypes = () => {
  const select = document.getElementById(ELEMENT_TYPE_SELECTOR_ID)
  // No type available in the configuration
  if (!select) return

  select.addEventListener('change', () => {
    SELECTED_TYPE.id = select.value
    SELECTED_TYPE.name = select.options[select.selectedIndex].text

    localStorage.setItem(LOCAL_STORAGE_ELEMENT_TYPE, SELECTED_TYPE.id)
  })

  // Init SELECTED_TYPE with the value stored in localStorage if it exists
  const storedTypeId = localStorage.getItem(LOCAL_STORAGE_ELEMENT_TYPE)
  if (storedTypeId) {
    const typeOption = getTypeOption(storedTypeId)
    if (typeOption) {
      select.value = storedTypeId
      select.dispatchEvent(new Event('change'))
    }
  }

  // If nothing was found in the localStorage, init SELECTED_TYPE with the first option
  if (!SELECTED_TYPE.id) select.dispatchEvent(new Event('change'))
}

export const SELECTED_TYPE = { id: '', name: '' }
