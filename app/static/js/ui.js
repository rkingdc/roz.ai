    // Toggle visibility of entire plugin sections based on enabled state AND active tab
    // File plugin is only visible in Chat tab if enabled
    elements.filePluginSection.classList.toggle('hidden', !isFileEnabled || activeTab !== 'chat');
    // Calendar plugin is only visible in Chat tab if enabled
    elements.calendarPluginSection.classList.toggle('hidden', !isCalendarEnabled || activeTab !== 'chat');
    // History plugin is only visible in Notes tab
    elements.historyPluginSection.classList.toggle('hidden', activeTab !== 'notes');
