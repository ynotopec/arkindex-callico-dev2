export const dispatchUpdateGroups = (groups) => {
  document.dispatchEvent(new CustomEvent(UPDATE_GROUPS_EVENT, { detail: groups }))
}

export const UPDATE_GROUPS_EVENT = 'update-groups'
export const UPDATE_GROUP_EVENT = 'update-group'
export const DELETE_GROUP_EVENT = 'delete-group'
