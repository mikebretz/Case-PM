// Copyright Sylvorin. All Rights Reserved.

#include "SylvorinGameMode.h"
#include "SylvorinCharacter.h"

ASylvorinGameMode::ASylvorinGameMode()
{
    DefaultPawnClass = ASylvorinCharacter::StaticClass();
}
