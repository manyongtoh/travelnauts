"""First names used to spot people in free text (Dutch and international, common in families travelling).

Used by the pseudonymiser together with the names known from the dossier. A capitalised word that is one
of these, or any word written as "Name (8)" or "Name van 8", is treated as a person's name.
"""
FIRST_NAMES = set("""
aaron abel adam adriaan aisha alexander alice amber amelia amy anna anne annemijn anouk anton arjen arthur astrid
bart bas beau benjamin bente bert bianca bo bob boris bram brian britt carlijn carmen caro casper cato charlie charlotte
chloe chris christiaan christopher claire cor daan daisy dani daniel danny david dean demi dewi dirk dex diego dina dylan
eef eline elin elisa elise elizabeth ella ellen elena elif emma emily emilia emre esmee esther eva evi evy
fabian fatima fay femke fenna finn fleur floor floris frank freek frederik fiene gabriel gijs guus hanna hannah hanneke
hans hidde hugo ilse imke inge ingrid ines iris isa isabel isabella ivo jack jacob jade jaimy jan janneke jasmijn jasper
jayden jens jeroen jesse jet jip job joep johan jonas joost joris josephine jorine julia julian julie juul kai karin
kees kevin kim koen lana lara lars laura lauren lea lena lennard lennert levi liam lieke lieve lily lina linde lisa lise
liv livia lizzy loes lola lot lotte louise luca lucas luuk lynn maarten maartje madelief maja marieke marit mark marleen
marloes martijn mats max maxime maud maya meike mees merel mia michael michiel mila milan milou mira mo mohammed nadia
naomi nathan nick niels niek nienke noa noah noor nora nina olaf olivia olivier oscar otis owen paula paul pepijn
pieter pim pip puck quinn rafael ralph remco rens rick rik rob robin roel roos rosa rosalie ruben rutger ruud saar
sam samantha sander sanne sara sarah saskia sebastiaan sem senna sep sevi siem simon sofia sophie stan stef stefan
stijn sven teun tessa thijs thomas tijn tim tom tobias tygo valerie vera veerle victor vince vincent wessel wim wouter
xavi yara yasmin yfke youssef yvonne zara zayn zoe zoë
ahmed ahmet anil anke anne-marie annelies annemarie annemieke ayoub ayse bilal catherine cynthia deepak douwe durk
edward emine esra fatma geert george gerrit gert giovanni glenn hafsa hamza harm harry henk henry hiroshi hylke
ibrahim imane ismail james jan-peter jan-willem jelle jermaine jessica joelle john jolien joop jorien joseph josien
joyce judith juliette karlijn kenji khadija kiran kirsten klaas laurien liesbeth lucy maaike manon
margaret marie marie-louise marjolein martine matthew megan mehmet merve mirjam mohamed monique
muhammad mustafa nguyen nour oliver omar ozlem petra piet pieter-jan priscilla priya rachel radj rajesh rebecca
renske rianne ricardo richard robert rodney rohit romano salma samira samuel sanjay shanti sharon shirley siebe
sietse simone sjoerd sunita suzanne tineke tjeerd victoria vishal wendy wietse william wilma winston yasmina
yasmine yuki yusuf zeynep
anja arjan chantal debby dennis edwin eric erik erwin  gerard hendrik ilona johannes jolanda kristel leon linda lisanne marcel marco mariska michel miranda mirella natasja nathalie nicole patrick peter renate ronald roy sabine sabrina sandra stephan wesley yvette
""".split())
