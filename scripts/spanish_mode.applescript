-- Source for "Modo espanol.app", the Spanish-mode launcher shipped in the .dmg.
-- Compiled by scripts/build_macos.sh with osacompile; see that file.
--
-- Why this exists: the default speech model, `small`, spells every Spanish word
-- correctly but drops accents on proper nouns and the opening question mark.
-- `medium` gets both right. Selecting it means setting an environment variable,
-- which is not a reasonable thing to ask a non-technical user to do, so this
-- wrapper does it for them. Double-click, and the real app starts with `medium`.
--
-- This bundle does NOT contain the app; it only launches it. That keeps it under
-- a megabyte instead of duplicating an 80 MB bundle.
--
-- The bundle identifier is tried first, so the launcher keeps working if the app
-- is renamed or filed somewhere other than /Applications. The name is the
-- fallback for the case where LaunchServices has not registered it yet.

on run
	set launched to false

	try
		do shell script "open --env STT_MODEL=medium -b com.mondragon.speechtotext"
		set launched to true
	end try

	if not launched then
		try
			do shell script "open --env STT_MODEL=medium -a SpeechToText"
			set launched to true
		end try
	end if

	if not launched then
		display dialog ¬
			"No se encuentra Speech to Text." & return & return & ¬
			"Arrastra SpeechToText a la carpeta Aplicaciones y ábrelo una vez. Después este atajo funcionará." & return & return & ¬
			"Speech to Text was not found. Drag SpeechToText to your Applications folder and open it once, then this shortcut will work." ¬
			buttons {"OK"} default button "OK" with title "Modo espanol" with icon caution
	end if
end run
