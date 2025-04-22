const storedTab = localStorage.getItem(config.ACTIVE_TAB_KEY);
state.setCurrentTab((storedTab === 'chat' || storedTab === 'notes') ? storedTab : 'chat');
