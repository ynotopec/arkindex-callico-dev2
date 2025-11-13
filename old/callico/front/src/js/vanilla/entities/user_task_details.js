import { displayEntities } from './base.js'

const MESSAGE_ATTRIBUTE = 'answer-entities'

export const bootEntitiesTranscriptionUserTaskDetails = (elementID) => {
  document.querySelectorAll('.message').forEach(message => {
    const transcription = message.querySelector('.message-body')
    const entities = JSON.parse(message.getAttribute(MESSAGE_ATTRIBUTE))
    displayEntities(null, null, transcription, entities[elementID], null)
  })
}
