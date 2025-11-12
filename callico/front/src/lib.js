// Base dependencies for the Django app
import 'bulma'
import * as Sentry from '@sentry/browser'
import { vueIntegration } from '@sentry/vue'

import { createApp } from 'vue'
import store from './js/store'

// Our Vue components
import InteractiveImage from './InteractiveImage.vue'
import ElementCarousel from './ElementCarousel.vue'
import ElementGroupManager from './ElementGroupManager.vue'

// Our style
import './css/style.css'
import '@creativebulma/bulma-tagsinput/dist/css/bulma-tagsinput.min.css'

// Our Vanilla JS code
import { bootCompletionTime } from './js/vanilla/annotations/completion_time.js'
import { bootUserTaskAnnotationStorage, cleanUserTaskAnnotationStorage } from './js/vanilla/annotations/storage.js'

import { bootClassificationAnnotate } from './js/vanilla/classification/annotate.js'
import { bootElementGroupAnnotate } from './js/vanilla/element_group/annotate.js'
import { bootElementsAnnotate } from './js/vanilla/elements/annotate.js'
import { bootEntityFormAnnotate } from './js/vanilla/entity_form/annotate.js'
import { bootEntitiesTranscriptionAnnotate } from './js/vanilla/entities/annotate.js'
import { bootTranscriptionAnnotate } from './js/vanilla/transcription/annotate.js'

import { bootElementGroupUserTaskDetails } from './js/vanilla/element_group/user_task_details.js'
import { bootElementsUserTaskDetails } from './js/vanilla/elements/user_task_details.js'
import { bootEntityFormUserTaskDetails } from './js/vanilla/entity_form/user_task_details.js'
import { bootEntitiesTranscriptionUserTaskDetails } from './js/vanilla/entities/user_task_details.js'
import { bootTranscriptionUserTaskDetails } from './js/vanilla/transcription/user_task_details.js'

import { bootArkindexImportForm } from './js/vanilla/forms/arkindex_import.js'
import { bootArkindexExportForm } from './js/vanilla/forms/arkindex_export.js'
import { bootCreateTasksForm } from './js/vanilla/forms/create_tasks.js'
import { bootEntityFormFieldForm } from './js/vanilla/forms/entity_form_field.js'
import { bootUpdateCampaignForm } from './js/vanilla/forms/update_campaign.js'

import { bootDropdowns } from './js/vanilla/utils/dropdown.js'
import { bootTextareaSizes } from './js/vanilla/utils/resize_textareas.js'
import { bootBulmaFileFields } from './js/vanilla/utils/bulma_file_fields.js'
import { bootBidiText } from './js/vanilla/utils/bidirectional_text.js'
import { bootCopyToClipboardButtons } from './js/vanilla/utils/copy_to_clipboard.js'
import { initCarouselLibraryEvents } from './js/vanilla/utils/carousel.js'
import { bootConfirmCampaignArchive } from './js/vanilla/utils/confirm_archive.js'

import { bootSentry } from './js/monitoring.js'

// Boot method for Vue components to avoid loading Vue.js globally
export const bootVueComponents = () => {
  const app = createApp({})

  // Track the Vue application using Sentry
  Sentry.addIntegration(vueIntegration({ app }))

  /*
   * Whitespace policy defaults to 'condense', but we want to use 'preserve' instead
   * https://vuejs.org/api/application.html#app-config-compileroptions-whitespace
   */
  app.config.compilerOptions.whitespace = 'preserve'

  // Add the store, the Vue components and mount the application
  app.use(store)
  app.component('InteractiveImage', InteractiveImage)
  app.component('ElementCarousel', ElementCarousel)
  app.component('ElementGroupManager', ElementGroupManager)
  app.mount('#app')
}

// Export Vanilla JS methods that are called by Django templates
export {
  // Global functions for annotation
  bootCompletionTime,
  bootUserTaskAnnotationStorage,
  cleanUserTaskAnnotationStorage,
  // Annotate
  bootClassificationAnnotate,
  bootElementGroupAnnotate,
  bootElementsAnnotate,
  bootEntitiesTranscriptionAnnotate,
  bootEntityFormAnnotate,
  bootTranscriptionAnnotate,
  // User task details
  bootElementGroupUserTaskDetails,
  bootElementsUserTaskDetails,
  bootEntitiesTranscriptionUserTaskDetails,
  bootEntityFormUserTaskDetails,
  bootTranscriptionUserTaskDetails,
  // Specific forms
  bootArkindexImportForm,
  bootArkindexExportForm,
  bootCreateTasksForm,
  bootEntityFormFieldForm,
  bootUpdateCampaignForm,
  // Utils
  bootDropdowns,
  bootTextareaSizes,
  bootBulmaFileFields,
  bootBidiText,
  bootCopyToClipboardButtons,
  initCarouselLibraryEvents,
  bootConfirmCampaignArchive,
  // Monitoring
  bootSentry
}
